#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Native shell for OPTSPOT AI.
//!
//! The window is a thin native frame around the SAME loopback page the browser
//! gets — there is no second implementation of the viewer, and no bundled web
//! assets beyond the ones the Python server already serves. The shell's only
//! real job is process lifetime:
//!
//!   * if a wash is already running, ATTACH to it and do not start a second
//!     one (same rule the skill follows) — and never kill a server we merely
//!     attached to
//!   * otherwise spawn the bundled server with whatever Python this machine
//!     has, read the tokenised URL it prints, and own it
//!   * on exit, close the server GRACEFULLY (an HTTP POST to its /close
//!     endpoint) so it removes its marker files — a hard kill would leave a
//!     stale marker and every later hook would pay for a doomed connect. Only
//!     if the graceful path fails does it escalate to a kill.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{Shutdown, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// `child: None` means "not ours" — we attached to a server someone else
/// started, and killing it on exit would yank the wash out from under
/// another window.
struct Server {
    child: Mutex<Option<Child>>,
    url: String,
}

/// Python candidates per platform. On Windows `python` may be the Microsoft
/// Store alias that exits without printing anything — that surfaces as an
/// empty first line and we simply try the next candidate.
#[cfg(not(windows))]
const PYTHONS: &[(&str, &[&str])] = &[("/usr/bin/python3", &[]), ("python3", &[])];
#[cfg(windows)]
const PYTHONS: &[(&str, &[&str])] = &[("python", &[]), ("python3", &[]), ("py", &["-3"])];

fn home() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

fn port_open(port: u16) -> bool {
    match format!("127.0.0.1:{}", port).parse() {
        Ok(addr) => TcpStream::connect_timeout(&addr, Duration::from_millis(250))
            .map(|s| {
                let _ = s.shutdown(Shutdown::Both);
            })
            .is_ok(),
        Err(_) => false,
    }
}

/// A stale marker file outlives an unclean shutdown, so the port is probed
/// rather than trusted.
fn existing() -> Option<String> {
    let raw =
        std::fs::read_to_string(home()?.join(".claude").join("agent-carwash").join("carwash.json"))
            .ok()?;
    let v: serde_json::Value = serde_json::from_str(&raw).ok()?;
    let url = v.get("url")?.as_str()?.to_string();
    let port = u16::try_from(v.get("port")?.as_u64()?).ok()?;
    if port_open(port) {
        Some(url)
    } else {
        None
    }
}

fn script_path(app: &tauri::AppHandle) -> Option<PathBuf> {
    if let Ok(dir) = app.path().resource_dir() {
        let p = dir.join("server").join("carwash_server.py");
        if p.exists() {
            return Some(p);
        }
    }
    // `tauri dev`: this crate lives at <repo>/desktop/src-tauri
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("server")
        .join("carwash_server.py");
    p.exists().then_some(p)
}

fn spawn_python(cmd: &str, extra: &[&str], script: &PathBuf) -> std::io::Result<Child> {
    let mut c = Command::new(cmd);
    c.args(extra)
        .arg(script)
        .arg("--no-browser")
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    c.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: no console flash
    c.spawn()
}

fn start(app: &tauri::AppHandle) -> Result<(String, Option<Child>), String> {
    if let Some(url) = existing() {
        return Ok((url, None));
    }
    let script = script_path(app).ok_or("carwash_server.py not found in app resources")?;

    let mut last_err = String::new();
    for (cmd, extra) in PYTHONS {
        let mut child = match spawn_python(cmd, extra, &script) {
            Ok(c) => c,
            Err(e) => {
                last_err = format!("{cmd}: {e}");
                continue;
            }
        };
        let out = match child.stdout.take() {
            Some(o) => o,
            None => {
                let _ = child.kill();
                continue;
            }
        };
        let mut reader = BufReader::new(out);
        let mut line = String::new();
        let _ = reader.read_line(&mut line);
        let url = line.trim().to_string();
        if url.starts_with("http://127.0.0.1:") {
            // Keep draining. The server only prints one line today, but a pipe
            // that fills would block it mid-ingest, and that failure would
            // look like "the wash froze" rather than "the shell stopped
            // reading".
            std::thread::spawn(move || {
                let mut sink = String::new();
                while reader.read_line(&mut sink).unwrap_or(0) > 0 {
                    sink.clear();
                }
            });
            return Ok((url, Some(child)));
        }
        // wrong or no output (e.g. the Store alias): not our Python
        let _ = child.kill();
        let _ = child.wait();
        last_err = format!("{cmd}: started but printed no loopback url");
    }

    #[cfg(windows)]
    let hint = "install Python 3 first (winget install Python.Python.3.12), then relaunch";
    #[cfg(not(windows))]
    let hint = "python3 was not found on PATH";
    Err(format!("could not start the OPTSPOT AI server — {hint} ({last_err})"))
}

/// Ask the server to shut itself down via its own /close endpoint, so it
/// removes its marker files. Plain-socket HTTP: no client dependency.
fn post_close(url: &str) -> Option<()> {
    let u = Url::parse(url).ok()?;
    let host = u.host_str()?.to_string();
    let port = u.port()?;
    let path = u.path().to_string(); // "/c/<token>/"
    let mut s = TcpStream::connect((host.as_str(), port)).ok()?;
    s.set_read_timeout(Some(Duration::from_millis(800))).ok()?;
    s.set_write_timeout(Some(Duration::from_millis(800))).ok()?;
    let req = format!(
        "POST {path}close HTTP/1.1\r\nHost: {host}:{port}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    );
    s.write_all(req.as_bytes()).ok()?;
    let mut buf = [0u8; 128];
    let _ = s.read(&mut buf);
    let _ = s.shutdown(Shutdown::Both);
    Some(())
}

fn stop(child: &mut Child, url: &str) {
    let _ = post_close(url);
    for _ in 0..40 {
        if matches!(child.try_wait(), Ok(Some(_))) {
            return;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    // graceful close ignored for 2 s: escalate. On unix SIGTERM still lets the
    // server clean its markers; elsewhere a hard kill is all that is left.
    #[cfg(unix)]
    {
        let _ = Command::new("kill")
            .arg("-TERM")
            .arg(child.id().to_string())
            .status();
        for _ in 0..20 {
            if matches!(child.try_wait(), Ok(Some(_))) {
                return;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle().clone();
            let (url, child) =
                start(&handle).map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
            let parsed = Url::parse(&url)?;
            app.manage(Server {
                child: Mutex::new(child),
                url,
            });

            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(parsed))
                .title("OPTSPOT AI")
                .inner_size(1460.0, 950.0)
                .min_inner_size(880.0, 600.0)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build OPTSPOT AI")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app.try_state::<Server>() {
                    let url = state.url.clone();
                    if let Some(mut child) = state.child.lock().unwrap().take() {
                        stop(&mut child, &url);
                    }
                }
            }
        });
}

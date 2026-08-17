use std::{env, process::{Child, Command}, sync::Mutex};

struct BackendProcess(Mutex<Option<Child>>);

impl Drop for BackendProcess {
    fn drop(&mut self) {
        if let Ok(process) = self.0.get_mut() {
            if let Some(child) = process.as_mut() {
                let _ = child.kill();
            }
        }
    }
}

fn start_backend() -> Option<Child> {
    let current = env::current_dir().ok()?;
    let root = current
        .ancestors()
        .find(|path| path.join("server/app.py").is_file())?;
    let python = root.join(".venv/bin/python");
    Command::new(python)
        .args(["-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", "8765"])
        .current_dir(root)
        .spawn()
        .ok()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(start_backend())))
        .run(tauri::generate_context!())
        .expect("error while running FormRender");
}

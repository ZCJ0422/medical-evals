import { execFileSync } from "node:child_process";
import path from "node:path";

export default function globalSetup() {
  const backendDir = path.resolve(__dirname, "../../backend");
  execFileSync("uv", ["run", "--no-sync", "python", path.join(__dirname, "seed_backend.py")], {
    cwd: backendDir, env: { ...process.env }, stdio: "inherit",
  });
}

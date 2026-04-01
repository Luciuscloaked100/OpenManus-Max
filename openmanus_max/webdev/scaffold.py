"""
OpenManus-Max Web Project Scaffold
一键生成 Web 项目脚手架
支持：static (HTML/CSS/JS), react (Vite+React+TS), api (FastAPI)
"""

from __future__ import annotations

import os
from typing import Optional

from openmanus_max.core.logger import logger
from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class WebScaffold(BaseTool):
    name: str = "web_scaffold"
    description: str = """Generate a web project scaffold with pre-configured templates.
Supported types:
- static: Simple HTML/CSS/JS project with Tailwind CSS
- react: Vite + React + TypeScript + Tailwind CSS project
- api: FastAPI + Python backend project with SQLite
Creates a complete project structure ready for development."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "Name of the project (used as directory name)",
            },
            "project_type": {
                "type": "string",
                "enum": ["static", "react", "api"],
                "description": "Type of web project to create",
            },
            "title": {
                "type": "string",
                "description": "Project title (for display)",
            },
            "description": {
                "type": "string",
                "description": "Brief project description",
            },
            "base_dir": {
                "type": "string",
                "description": "Base directory to create project in (default: workspace)",
            },
        },
        "required": ["project_name", "project_type"],
    }

    async def execute(
        self,
        project_name: str,
        project_type: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        base_dir: Optional[str] = None,
    ) -> ToolResult:
        from openmanus_max.core.config import get_config
        base = base_dir or get_config().workspace_dir
        project_dir = os.path.join(base, project_name)

        if os.path.exists(project_dir):
            return self.fail(f"Directory already exists: {project_dir}")

        title = title or project_name
        description = description or f"A {project_type} web project"

        try:
            if project_type == "static":
                self._create_static(project_dir, title, description)
            elif project_type == "react":
                self._create_react(project_dir, title, description)
            elif project_type == "api":
                self._create_api(project_dir, title, description)
            else:
                return self.fail(f"Unknown project type: {project_type}")

            # 统计文件
            file_count = sum(len(files) for _, _, files in os.walk(project_dir))
            return self.success(
                f"Project '{project_name}' created at: {project_dir}\n"
                f"Type: {project_type}\n"
                f"Files: {file_count}\n"
                f"Next steps: cd {project_dir} && see README.md"
            )

        except Exception as e:
            return self.fail(f"Scaffold creation failed: {str(e)}")

    def _create_static(self, path: str, title: str, desc: str):
        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, "css"), exist_ok=True)
        os.makedirs(os.path.join(path, "js"), exist_ok=True)
        os.makedirs(os.path.join(path, "assets"), exist_ok=True)

        # index.html
        with open(os.path.join(path, "index.html"), "w") as f:
            f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="css/style.css">
</head>
<body class="bg-gray-50 min-h-screen">
    <nav class="bg-white shadow-sm border-b">
        <div class="max-w-7xl mx-auto px-4 py-3">
            <h1 class="text-xl font-bold text-gray-800">{title}</h1>
        </div>
    </nav>
    <main class="max-w-7xl mx-auto px-4 py-8">
        <div class="bg-white rounded-lg shadow p-6">
            <h2 class="text-2xl font-semibold mb-4">Welcome</h2>
            <p class="text-gray-600">{desc}</p>
        </div>
    </main>
    <script src="js/app.js"></script>
</body>
</html>
""")
        with open(os.path.join(path, "css", "style.css"), "w") as f:
            f.write("/* Custom styles */\n")
        with open(os.path.join(path, "js", "app.js"), "w") as f:
            f.write("// Application logic\nconsole.log('App loaded');\n")
        self._write_readme(path, title, desc, "static")

    def _create_react(self, path: str, title: str, desc: str):
        os.makedirs(os.path.join(path, "src", "components"), exist_ok=True)
        os.makedirs(os.path.join(path, "public"), exist_ok=True)

        # package.json
        with open(os.path.join(path, "package.json"), "w") as f:
            f.write(f"""{{"name": "{os.path.basename(path)}",
  "private": true, "version": "0.1.0", "type": "module",
  "scripts": {{
    "dev": "vite", "build": "tsc && vite build", "preview": "vite preview"
  }},
  "dependencies": {{
    "react": "^18.3.1", "react-dom": "^18.3.1"
  }},
  "devDependencies": {{
    "@types/react": "^18.3.0", "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0", "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38", "tailwindcss": "^3.4.4",
    "typescript": "^5.5.0", "vite": "^5.3.0"
  }}
}}
""")
        # vite.config.ts
        with open(os.path.join(path, "vite.config.ts"), "w") as f:
            f.write("""import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({ plugins: [react()] })
""")
        # tsconfig.json
        with open(os.path.join(path, "tsconfig.json"), "w") as f:
            f.write("""{"compilerOptions": {"target": "ES2020", "useDefineForClassFields": true,
  "lib": ["ES2020", "DOM", "DOM.Iterable"], "module": "ESNext",
  "skipLibCheck": true, "moduleResolution": "bundler", "allowImportingTsExtensions": true,
  "resolveJsonModule": true, "isolatedModules": true, "noEmit": true, "jsx": "react-jsx",
  "strict": true, "noUnusedLocals": true, "noUnusedParameters": true, "noFallthroughCasesInSwitch": true
}, "include": ["src"]}
""")
        # tailwind.config.js
        with open(os.path.join(path, "tailwind.config.js"), "w") as f:
            f.write("""/** @type {import('tailwindcss').Config} */
export default { content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} }, plugins: [] }
""")
        # postcss.config.js
        with open(os.path.join(path, "postcss.config.js"), "w") as f:
            f.write("export default { plugins: { tailwindcss: {}, autoprefixer: {} } }\n")
        # index.html
        with open(os.path.join(path, "index.html"), "w") as f:
            f.write(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title}</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>
""")
        # src/main.tsx
        with open(os.path.join(path, "src", "main.tsx"), "w") as f:
            f.write("""import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
""")
        # src/App.tsx
        with open(os.path.join(path, "src", "App.tsx"), "w") as f:
            f.write(f"""export default function App() {{
  return (<div className="min-h-screen bg-gray-50">
    <nav className="bg-white shadow-sm border-b"><div className="max-w-7xl mx-auto px-4 py-3">
      <h1 className="text-xl font-bold">{title}</h1></div></nav>
    <main className="max-w-7xl mx-auto px-4 py-8"><div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-2xl font-semibold mb-4">Welcome</h2>
      <p className="text-gray-600">{desc}</p></div></main></div>)
}}
""")
        # src/index.css
        with open(os.path.join(path, "src", "index.css"), "w") as f:
            f.write("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n")
        self._write_readme(path, title, desc, "react")

    def _create_api(self, path: str, title: str, desc: str):
        os.makedirs(os.path.join(path, "app", "routes"), exist_ok=True)
        os.makedirs(os.path.join(path, "app", "models"), exist_ok=True)

        # requirements.txt
        with open(os.path.join(path, "requirements.txt"), "w") as f:
            f.write("fastapi>=0.110.0\nuvicorn>=0.29.0\nsqlalchemy>=2.0.0\npydantic>=2.0.0\n")
        # app/__init__.py
        with open(os.path.join(path, "app", "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(path, "app", "routes", "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(path, "app", "models", "__init__.py"), "w") as f:
            f.write("")
        # app/main.py
        with open(os.path.join(path, "app", "main.py"), "w") as f:
            f.write(f"""from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="{title}", description="{desc}")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
async def root():
    return {{"message": "Welcome to {title}", "status": "running"}}

@app.get("/health")
async def health():
    return {{"status": "ok"}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
""")
        # app/database.py
        with open(os.path.join(path, "app", "database.py"), "w") as f:
            f.write("""from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
""")
        self._write_readme(path, title, desc, "api")

    def _write_readme(self, path: str, title: str, desc: str, ptype: str):
        instructions = {
            "static": "Open `index.html` in your browser.",
            "react": "```bash\npnpm install\npnpm dev\n```",
            "api": "```bash\npip install -r requirements.txt\npython -m app.main\n```",
        }
        with open(os.path.join(path, "README.md"), "w") as f:
            f.write(f"# {title}\n\n{desc}\n\n## Getting Started\n\n{instructions[ptype]}\n")

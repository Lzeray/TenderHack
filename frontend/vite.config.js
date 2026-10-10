import { defineConfig } from "vite";

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/static/" : "/",
  // Сборка сразу в каталог, который раздаёт FastAPI (ktru_assist/web); старые файлы не удаляются.
  build: { outDir: "../ktru_assist/web", emptyOutDir: false },
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/health": "http://127.0.0.1:8000" } },
}));

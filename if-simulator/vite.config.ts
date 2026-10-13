import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // 相对路径构建：产物可在任意子路径下通过 HTTP 提供
  // （注意：仍**不能**用 file:// 直接打开 —— ES Module 受 CORS 限制，
  //  必须经 HTTP。便携启动脚本见 ../启动模拟器.bat）
  base: './',
  server: { port: 5173 },
  preview: { port: 4173 },
});

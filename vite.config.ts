import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Relative assets work at username.github.io/ and username.github.io/repository/.
  // All application routes live after #, so they never change the asset base.
  base: "./",
});

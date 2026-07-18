// Build the self-contained workflow-editor bundle with esbuild.
// Emits editor.bundle.js (+ editor.bundle.css) into the app's static directory.
import * as esbuild from "esbuild";

const outdir = "../job_orchestrator/static/job_orchestrator/js";

const options = {
  entryPoints: ["src/index.tsx"],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2020"],
  loader: { ".css": "css" },
  outfile: `${outdir}/editor.bundle.js`,
  logLevel: "info",
  // React, ReactDOM and @xyflow/react are intentionally bundled so the page is self-contained.
};

if (process.argv.includes("--watch")) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
  console.log("watching for changes…");
} else {
  await esbuild.build(options);
}

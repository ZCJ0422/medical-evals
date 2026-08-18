/**
 * Keep development and production artifacts separate. Running `next build`
 * while `next dev` is serving the app must not invalidate the dev server's
 * webpack runtime files.
 */
const isProduction = process.env.NODE_ENV === "production";

/** @type {import("next").NextConfig} */
const nextConfig = {
  distDir: isProduction ? ".next-build" : ".next",
};

export default nextConfig;

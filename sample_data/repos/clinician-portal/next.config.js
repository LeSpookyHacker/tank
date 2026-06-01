/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // TODO(appsec): add security headers (CSP, HSTS, X-Frame-Options) — tracked in
  // the secure-SDLC backlog. Currently relying on Cloud Armor at the edge only.
  output: "standalone",
};
module.exports = nextConfig;

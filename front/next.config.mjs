/** @type {import('next').NextConfig} */

// Le front proxifie /api vers Flask : une seule origine côté navigateur, donc la
// session Flask (cookie) fonctionne sans CORS. Override possible via BACKEND_URL.
const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:5000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;

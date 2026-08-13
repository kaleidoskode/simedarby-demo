import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Traces the exact modules the server needs, so the Docker runtime stage can
  // ship without node_modules.
  output: "standalone",
};

export default nextConfig;

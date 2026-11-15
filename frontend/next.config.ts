import type { NextConfig } from 'next'

// Static export: hasil build disajikan oleh server/app.py (Python) yang
// sama dengan API-nya, jadi deploy tetap satu container dan satu port.
const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
}

export default nextConfig

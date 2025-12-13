/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Permite fetch de APIs externas
  async headers() {
    return [
      {
        source: '/api/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
        ],
      },
    ]
  },
}

module.exports = nextConfig

import type { CapacitorConfig } from '@capacitor/cli'

// Bundle the existing React UI. API URLs and auth belong to the application
// transport, never server.url (which would replace the UI with a remote site).
const config: CapacitorConfig = {
  appId: 'in.nyaysaathi.app',
  appName: 'Nyay Saathi',
  webDir: 'dist',
  server: { androidScheme: 'https', cleartext: false },
  android: { allowMixedContent: false },
}

export default config

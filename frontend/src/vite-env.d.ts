/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  /** Vollständige Backend-URL für Cross-Origin-Deployments, z. B. https://api.example.com. */
  readonly VITE_API_BASE_URL?: string;
  /** Öffentliche Pages-URL für Supabase-Auth-Redirects. */
  readonly VITE_PUBLIC_APP_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.png" {
  const content: string;
  export default content;
}

declare module "*.jpg" {
  const content: string;
  export default content;
}

declare module "*.jpeg" {
  const content: string;
  export default content;
}

declare module "*.svg" {
  const content: string;
  export default content;
}

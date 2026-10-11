import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

// Keep the Supabase session in persistent browser storage so closing/reopening
// the storefront does not sign the user out. Only supabase.auth.signOut() logs out.
export const supabase = url && key ? createClient(url, key, {
  auth: {
    persistSession: true,
    storage: window.localStorage,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
}) : null

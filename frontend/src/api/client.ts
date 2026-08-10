import createClient from "openapi-fetch";
import type { paths } from "./schema";

// Falls back to the Compose/dev default so a clean clone works with no .env
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const api = createClient<paths>({ baseUrl: API_BASE });

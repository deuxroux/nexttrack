import { useState } from "react";
import { api } from "../api/client";
import type { components } from "../api/schema";

type RecommendParams = components["schemas"]["RecommendationParams"];
type Track = components["schemas"]["Track"];

export function useRecommend() {
    const [data, setData] = useState<components["schemas"]["RecommendationResult"] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function recommend(seeds: Track[], params: RecommendParams) {
        setLoading(true);
        setError(null);
        const { data, error } = await api.POST("/recommend", {
            body: { seeds, params },
        });
        setLoading(false);
        if (error) {
            const errObj = error as unknown;
            setError(
                typeof errObj === "object" && errObj !== null && "detail" in errObj
                    ? String((errObj as { detail: unknown }).detail)
                    : "Request failed"
            );
            return;
        }
        setData((data as components["schemas"]["RecommendationResult"] | undefined) ?? null);
    }

    return { data, error, loading, recommend };
}

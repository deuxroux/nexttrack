import { useRecommend } from "../hooks/useRecommend";

export function RecommendForm() {
    const { data, error, loading, recommend } = useRecommend();

    function handleSubmit() {
        recommend(
            [{ artist: "Radiohead", title: "Karma Police" }],
            { novelty: 50, artist_diversity: 3, length: 10, genre_lock: [] }
        );
    }

    return (
        <div>
            <button onClick={handleSubmit} disabled={loading}>
                {loading ? "Loading..." : "Get Recommendations"}
            </button>
            {error && <p role="alert">{error}</p>}
            {data && <pre>{JSON.stringify(data.candidates, null, 2)}</pre>}
        </div>
    );
}

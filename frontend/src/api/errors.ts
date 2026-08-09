export function mapRecommendError(status: number, errorCode?: string): string {
  if (status === 422 && errorCode === "no_successful_seeds")
    return "None of your seed tracks match Last.fm hits. Try different tracks.";
  if (status === 422 && errorCode === "no_recommendations")
    return "No tracks match your filters. Loosen genre-lock or novelty.";
  if (status === 502 && errorCode === "lastfm_unavailable")
    return "Last.fm not responding. Try again later.";
  return "Something went wrong. Please try again.";
}

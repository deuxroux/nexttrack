export function mapRecommendErrorCode(errorCode?: string): string {
  switch (errorCode) {
    case "no_successful_seeds":
      return "None of your seed tracks match Last.fm hits. Try different tracks.";
    case "no_recommendations":
      return "No tracks match your filters. Loosen genre-lock or novelty.";
    case "lastfm_unavailable":
      return "Last.fm not responding. Try again later.";
    default:
      return "Something went wrong. Please try again.";
  }
}

export function mapRecommendError(status: number, errorCode?: string): string {
  if (status === 422 && errorCode === "no_successful_seeds")
    return mapRecommendErrorCode(errorCode);
  if (status === 422 && errorCode === "no_recommendations")
    return mapRecommendErrorCode(errorCode);
  if (status === 502 && errorCode === "lastfm_unavailable")
    return mapRecommendErrorCode(errorCode);
  return "Something went wrong. Please try again.";
}

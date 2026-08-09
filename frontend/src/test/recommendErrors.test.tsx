import { render, screen } from "@testing-library/react";
import { ParamsPanel } from "../components/ParamsPanel";
import { useParams } from "../hooks/useParams";
import type { SeedProfileHandle } from "../hooks/useSeedProfile";
import type { SeedsHandle } from "../hooks/useSeeds";

// mapError in useRecommendStream. test output via ui, not here

const emptySeeds: SeedsHandle = {
  seeds: [],
  count: 0,
  atCap: false,
  canRecommend: false,
  add: vi.fn(),
  remove: vi.fn(),
};

const emptyProfile: SeedProfileHandle = {
  tags: [],
  loading: false,
  error: null,
  fetchProfile: vi.fn(),
};

function ErrorPanel({ error }: { error: string }) {
  const params = useParams();
  return (
    <ParamsPanel
      params={params}
      profile={emptyProfile}
      seeds={emptySeeds}
      onRecommend={() => { }}
      streaming={false}
      progress={null}
      error={error}
    />
  );
}

describe("Recommendation error messages", () => {
  it("no_successful_seeds → correct message", () => {
    render(
      <ErrorPanel error="None of your seed tracks match Last.fm hits. Try different tracks." />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /None of your seed tracks/i,
    );
  });

  it("no_recommendations → correct message", () => {
    render(
      <ErrorPanel error="No tracks match your filters. Loosen genre-lock or novelty." />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /No tracks match your filters/i,
    );
  });

  it("lastfm_unavailable → correct message", () => {
    render(<ErrorPanel error="Last.fm is not responding. Try again shortly." />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      /Last\.fm is not responding/i,
    );
  });
});

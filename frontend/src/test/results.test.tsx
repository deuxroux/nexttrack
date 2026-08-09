import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { Results } from "../components/Results";
import type { components } from "../api/schema";

type RecommendationResult = components["schemas"]["RecommendationResult"];

const mockResult: RecommendationResult = {
  candidates: [
    {
      artist: "Portishead",
      title: "Glory Box",
      summed_similarity: 0.85,
      tag_overlap: 2,
      novelty_bonus: 0.1,
      final_score: 0.9,
      contributing_seeds: ["Radiohead — Pyramid Song"],
      matched_tags: ["trip-hop", "electronic"],
      explanation: ["Similar to Radiohead — Pyramid Song", "Matched tags: trip-hop, electronic"],
    },
  ],
  dropped_seeds: [],
  params: { novelty: 60, artist_diversity: 3, length: 10, genre_lock: [] },
  pool_exhausted: false,
};

describe("Results (3.23)", () => {
  it("renders candidate title, artist, matched_tags, and explanation", () => {
    render(
      <Results result={mockResult} onExport={vi.fn()} exporting={false} exportError={null} />,
    );
    expect(screen.getByText("Glory Box")).toBeInTheDocument();
    expect(screen.getByText("Portishead")).toBeInTheDocument();
    expect(screen.getByText("trip-hop")).toBeInTheDocument();
    expect(screen.getByText("electronic")).toBeInTheDocument();
    expect(screen.getByText(/Similar to Radiohead/)).toBeInTheDocument();
  });

  it("shows pool_exhausted notice when pool is exhausted (2.11)", () => {
    render(
      <Results
        result={{ ...mockResult, pool_exhausted: true }}
        onExport={vi.fn()}
        exporting={false}
        exportError={null}
      />,
    );
    expect(screen.getByText(/candidate pool was exhausted/i)).toBeInTheDocument();
  });

  it("does not show exhausted notice when pool is not exhausted", () => {
    render(
      <Results result={mockResult} onExport={vi.fn()} exporting={false} exportError={null} />,
    );
    expect(screen.queryByText(/candidate pool was exhausted/i)).not.toBeInTheDocument();
  });

  it("renders empty state and disabled Export when result is null", () => {
    render(
      <Results result={null} onExport={vi.fn()} exporting={false} exportError={null} />,
    );
    expect(screen.getByText(/Add seeds and click Recommend/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export csv/i })).toBeDisabled();
  });

  it("Export CSV button is enabled when result is present", () => {
    render(
      <Results result={mockResult} onExport={vi.fn()} exporting={false} exportError={null} />,
    );
    expect(screen.getByRole("button", { name: /export csv/i })).not.toBeDisabled();
  });

  it("shows export error message when exportError is set", () => {
    render(
      <Results
        result={mockResult}
        onExport={vi.fn()}
        exporting={false}
        exportError="Something went wrong. Please try again."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/something went wrong/i);
  });
});

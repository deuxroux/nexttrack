import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { components } from "../api/schema";
import { Results } from "../components/Results";

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

  it("renders per-track similarity badge with percentage", () => {
    // summed_similarity=0.85, contributing_seeds.length=1 → 85% match
    render(
      <Results result={mockResult} onExport={vi.fn()} exporting={false} exportError={null} />,
    );
    expect(screen.getByText("85% match")).toBeInTheDocument();
  });

  it("renders average similarity footer matching single-candidate result", () => {
    render(
      <Results result={mockResult} onExport={vi.fn()} exporting={false} exportError={null} />,
    );
    expect(screen.getByText("Avg. similarity: 85%")).toBeInTheDocument();
  });

  it("computes correct average similarity across multiple candidates", () => {
    //case for combined (multi-track) contribution of a result. average over multiple seeds
    const multiResult: RecommendationResult = {
      ...mockResult,
      candidates: [
        { ...mockResult.candidates[0], summed_similarity: 0.80, contributing_seeds: ["Radiohead — Pyramid Song"] },
        {
          artist: "Massive Attack",
          title: "Teardrop",
          summed_similarity: 0.60,
          tag_overlap: 1,
          novelty_bonus: 0.2,
          final_score: 0.7,
          contributing_seeds: ["Radiohead — Pyramid Song"],
          matched_tags: ["trip-hop"],
          explanation: ["Similar to Radiohead — Pyramid Song"],
        },
      ],
    };
    render(
      <Results result={multiResult} onExport={vi.fn()} exporting={false} exportError={null} />,
    );
    expect(screen.getByText("Avg. similarity: 70%")).toBeInTheDocument();
  });

  it("guards against zero division when contributing_seeds is empty", () => {
    const guardResult: RecommendationResult = {
      ...mockResult,
      candidates: [
        { ...mockResult.candidates[0], contributing_seeds: [] },
      ],
    };
    render(
      <Results result={guardResult} onExport={vi.fn()} exporting={false} exportError={null} />,
    );
    // confirm badge still renders a numeric percentage
    //todo make sure this value makes sense in a real scenario
    expect(screen.getByText(/\d+% match/)).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});

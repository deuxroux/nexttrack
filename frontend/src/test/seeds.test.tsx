import { act, renderHook } from "@testing-library/react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { SeedBuilder } from "../components/SeedBuilder";
import { useSeeds } from "../hooks/useSeeds";

// hoisted so factory fn and test bodies share the same mock references
const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: { GET: mockGet, POST: mockPost },
}));

// minimal wrapper that supplies a fresh useSeeds instance to SeedBuilder
function Wrapper() {
  const seeds = useSeeds();
  return <SeedBuilder seeds={seeds} />;
}

// ── useSeeds cap enforcement (3.10) ──────────────────────────────────────────

describe("useSeeds — cap and capacity", () => {
  it("blocks add at 50 seeds", () => {
    const { result } = renderHook(() => useSeeds());
    for (let i = 0; i < 50; i++) {
      act(() => result.current.add({ artist: `A${i}`, title: `T${i}` }));
    }
    expect(result.current.atCap).toBe(true);
    expect(result.current.count).toBe(50);
    act(() => result.current.add({ artist: "Extra", title: "Track" }));
    expect(result.current.count).toBe(50);
  });

  it("removing one seed restores capacity", () => {
    const { result } = renderHook(() => useSeeds());
    for (let i = 0; i < 50; i++) {
      act(() => result.current.add({ artist: `A${i}`, title: `T${i}` }));
    }
    act(() => result.current.remove(0));
    expect(result.current.atCap).toBe(false);
    expect(result.current.count).toBe(49);
  });

  it("canRecommend is false with no seeds", () => {
    const { result } = renderHook(() => useSeeds());
    expect(result.current.canRecommend).toBe(false);
    act(() => result.current.add({ artist: "A", title: "B" }));
    expect(result.current.canRecommend).toBe(true);
  });
});

// ── SeedBuilder Spotify fallback (3.31) ──────────────────────────────────────

describe("SeedBuilder — Spotify URL fallback", () => {
  it("failed resolve shows fallback notice and does not add a seed", async () => {
    // 400/502 — error path
    mockPost.mockResolvedValue({ data: undefined, error: { detail: "not found" } });

    const user = userEvent.setup();
    render(<Wrapper />);

    await user.type(
      screen.getByLabelText(/spotify track url/i),
      "https://open.spotify.com/track/abc123",
    );
    await user.click(screen.getByRole("button", { name: /add track from spotify url/i }));

    expect(await screen.findByText(/couldn't resolve/i)).toBeInTheDocument();
    // counter must still show 0 — no seed was added
    expect(screen.getByText("0 / 50 tracks")).toBeInTheDocument();
  });
});

// ── SeedBuilder search + select (3.08, 3.11) ─────────────────────────────────

describe("SeedBuilder — search and select", () => {
  it("typing triggers a search and selecting a result adds it as a seed", async () => {
    mockGet.mockResolvedValue({
      data: [{ artist: "Radiohead", title: "Creep", image: null }],
    });

    const user = userEvent.setup();
    render(<Wrapper />);

    await user.type(screen.getByRole("combobox"), "Cre");

    // dropdown option should appear after the debounce resolves
    const option = await screen.findByRole("option", { name: /Creep/i });
    await user.click(option);

    // seed should appear in the list with a remove button
    expect(
      screen.getByRole("button", { name: /Remove Creep by Radiohead/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 / 50 tracks")).toBeInTheDocument();
  });
});

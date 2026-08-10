import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import App from "../App";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: { GET: mockGet, POST: mockPost },
  API_BASE: "http://localhost:8000",
}));

// Capture onmessage so tests can fire synthetic SSE events
const streamState = vi.hoisted(() => ({
  onmessage: null as ((ev: { event: string; data: string }) => void) | null,
}));

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(
    (
      _url: string,
      opts: { onmessage?: (ev: { event: string; data: string }) => void },
    ) => {
      streamState.onmessage = opts.onmessage ?? null;
      return new Promise<void>(() => { }); // hangs — simulates open stream
    },
  ),
}));

beforeEach(() => {
  streamState.onmessage = null;
  mockGet.mockImplementation((path: string) => {
    if (path === "/health") return Promise.resolve({ data: { status: "ok" } });
    // search results for typeahead
    return Promise.resolve({
      data: [{ artist: "Radiohead", title: "Creep", image: null }],
    });
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

//Fixturing for re-set conditions-- mock recommendations matching shape of candidates.
const mockResult = {
  candidates: [
    {
      artist: "Portishead",
      title: "Glory Box",
      summed_similarity: 0.9,
      tag_overlap: 3,
      novelty_bonus: 0.1,
      final_score: 1.0,
      contributing_seeds: ["Radiohead|Creep"],
      matched_tags: ["trip-hop"],
      explanation: ["High similarity"],
    },
  ],
  dropped_seeds: [],
  params: { novelty: 50, genre_lock: [], artist_diversity: 5, length: 10 },
  pool_exhausted: false,
};

describe("useRecommendStream — SSE done event", () => {
  it("done event re-enables Recommend after successful stream", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByRole("combobox"), "Cre");
    const option = await screen.findByRole("option", { name: /Creep/i });
    await user.click(option);

    await user.click(screen.getByRole("button", { name: /^Recommend$/i }));

    await act(async () => {
      streamState.onmessage!({ event: "result", data: JSON.stringify(mockResult) });
    });
    await act(async () => {
      streamState.onmessage!({ event: "done", data: "{}" });
    });

    expect(screen.getByRole("button", { name: /^Recommend$/i })).not.toBeDisabled();
  });
});

describe("useRecommendStream — SSE error event", () => {
  it("error event surfaces mapped message and re-enables Recommend", async () => {
    const user = userEvent.setup();
    render(<App />);

    // typeahead so canRecommend becomes true
    await user.type(screen.getByRole("combobox"), "Cre");
    const option = await screen.findByRole("option", { name: /Creep/i });
    await user.click(option);

    // on recommend click fetchEventSource is now called and opts captured
    await user.click(screen.getByRole("button", { name: /^Recommend$/i }));

    // simulate server emitting an error SSE event mid-stream
    await act(async () => {
      streamState.onmessage!({
        event: "error",
        data: JSON.stringify({ error: "no_recommendations" }),
      });
    });

    // alert should show the mapped human-readable message
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No tracks match your filters. Loosen genre-lock or novelty.",
    );
    //confirm  Recommend button is re-enabled
    expect(screen.getByRole("button", { name: /^Recommend$/i })).not.toBeDisabled();
  });
});

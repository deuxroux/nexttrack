import { act, renderHook } from "@testing-library/react";
import { vi } from "vitest";
import type { components } from "../api/schema";
import { useCsvExport } from "../hooks/useCsvExport";

type Track = components["schemas"]["Track"];
type RecommendationParams = components["schemas"]["RecommendationParams"];

const seeds: Track[] = [{ artist: "Radiohead", title: "Pyramid Song" }];
const params: RecommendationParams = {
  novelty: 60,
  artist_diversity: 3,
  length: 10,
  genre_lock: [],
};

beforeEach(() => {
  globalThis.URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
  globalThis.URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("useCsvExport", () => {
  it("reads filename from Content-Disposition and triggers anchor download", async () => {
    const mockBlob = new Blob(["artist,title\nRadiohead,Creep"], { type: "text/csv" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(mockBlob),
        headers: new Headers({
          "Content-Disposition": 'attachment; filename="nexttrack_2026-08-06_nov60_div3.csv"',
        }),
      }),
    );

    // capture anchor.download
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      function (this: HTMLAnchorElement) {
        clicks.push(this.download);
      },
    );

    const { result } = renderHook(() => useCsvExport());
    await act(async () => {
      await result.current.export(seeds, params);
    });

    expect(clicks[0]).toBe("nexttrack_2026-08-06_nov60_div3.csv");
    expect(URL.createObjectURL).toHaveBeenCalledWith(mockBlob);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
    expect(result.current.error).toBeNull();
    expect(result.current.exporting).toBe(false);
  });

  it("falls back to nexttrack_export.csv when Content-Disposition is absent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob([""])),
        headers: new Headers(),
      }),
    );
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      function (this: HTMLAnchorElement) {
        clicks.push(this.download);
      },
    );

    const { result } = renderHook(() => useCsvExport());
    await act(async () => {
      await result.current.export(seeds, params);
    });

    expect(clicks[0]).toBe("nexttrack_export.csv");
  });

  it("surfaces mapped error message on non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: () => Promise.resolve({ error: "no_successful_seeds" }),
      }),
    );

    const { result } = renderHook(() => useCsvExport());
    await act(async () => {
      await result.current.export(seeds, params);
    });

    expect(result.current.error).toMatch(/None of your seed tracks match Last\.fm hits/i);
    expect(result.current.exporting).toBe(false);
  });
});

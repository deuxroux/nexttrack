import { act, renderHook } from "@testing-library/react";
import { useParams } from "../hooks/useParams";

describe("useParams bounds and serialisation", () => {
  it("clamps novelty below 0 and above 100", () => {
    const { result } = renderHook(() => useParams());
    act(() => result.current.setNovelty(-10));
    expect(result.current.novelty).toBe(0);
    act(() => result.current.setNovelty(200));
    expect(result.current.novelty).toBe(100);
  });

  it("clamps artistDiversity below 1 and above 10", () => {
    const { result } = renderHook(() => useParams());
    act(() => result.current.setArtistDiversity(0));
    expect(result.current.artistDiversity).toBe(1);
    act(() => result.current.setArtistDiversity(99));
    expect(result.current.artistDiversity).toBe(10);
  });

  it("clamps length below 5 and above 50", () => {
    const { result } = renderHook(() => useParams());
    act(() => result.current.setLength(1));
    expect(result.current.length).toBe(5);
    act(() => result.current.setLength(100));
    expect(result.current.length).toBe(50);
  });

  it("toParams returns the correct schema field names", () => {
    const { result } = renderHook(() => useParams());
    act(() => {
      result.current.setNovelty(70);
      result.current.setArtistDiversity(5);
      result.current.setLength(20);
      result.current.addGenreLock("indie");
    });
    expect(result.current.toParams()).toEqual({
      novelty: 70,
      artist_diversity: 5,
      length: 20,
      genre_lock: ["indie"],
    });
  });

  it("genreLock is dedupe", () => {
    const { result } = renderHook(() => useParams());
    act(() => {
      result.current.addGenreLock("Rock");
      result.current.addGenreLock("rock");
      result.current.addGenreLock("ROCK");
    });
    expect(result.current.genreLock).toHaveLength(1);
    expect(result.current.genreLock[0]).toBe("Rock"); // preserves first one
  });

  it("removeGenreLock is case-insensitive", () => {
    const { result } = renderHook(() => useParams());
    act(() => result.current.addGenreLock("Jazz"));
    act(() => result.current.removeGenreLock("jazz"));
    expect(result.current.genreLock).toHaveLength(0);
  });
});

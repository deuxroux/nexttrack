import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ParamsPanel } from "../components/ParamsPanel";
import { useParams } from "../hooks/useParams";
import { useSeedProfile } from "../hooks/useSeedProfile";
import type { SeedsHandle } from "../hooks/useSeeds";

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn() }));
vi.mock("../api/client", () => ({
  api: { GET: vi.fn(), POST: mockPost },
}));

// minimal seed tet canRecommend=true. output is Suggest button is enabled
const mockSeeds: SeedsHandle = {
  seeds: [{ artist: "Radiohead", title: "Creep" }],
  count: 1,
  atCap: false,
  canRecommend: true,
  add: vi.fn(),
  remove: vi.fn(),
};

function Wrapper() {
  const params = useParams();
  const profile = useSeedProfile();
  return (
    <ParamsPanel
      params={params}
      profile={profile}
      seeds={mockSeeds}
      onRecommend={() => { }}
      streaming={false}
      progress={null}
      error={null}
    />
  );
}

describe("ParamsPanel — genre-lock via seed-profile", () => {
  it("renders suggested tag chips and clicking one adds it to genreLock", async () => {
    mockPost.mockResolvedValue({
      data: {
        tags: [
          { name: "indie rock", seed_count: 3 },
          { name: "alternative", seed_count: 2 },
        ],
        dropped_seeds: [],
        total_seeds: 1,
      },
    });

    const user = userEvent.setup();
    render(<Wrapper />);

    // suggest button is enabled?
    await user.click(screen.getByRole("button", { name: /suggest genres from seeds/i }));

    // chips  appear after POST?
    const chip = await screen.findByRole("button", { name: /^indie rock$/i });
    expect(chip).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^alternative$/i })).toBeInTheDocument();

    // cselecting chip locks it?
    await user.click(chip);
    expect(
      screen.getByRole("button", { name: /Remove genre indie rock/i }),
    ).toBeInTheDocument();
  });
});

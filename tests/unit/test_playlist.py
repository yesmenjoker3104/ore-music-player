import pytest

from ore_music_player.domain.models import Playlist, Track


def make_track(track_id: str) -> Track:
    return Track(
        track_id=track_id,
        path=f"{track_id}.mp3",
        title=track_id,
    )

def make_playlist() -> Playlist:
    return Playlist(
        playlist_id="playlist_1",
        name="My Playlist",
    )


def test_playlist_adds_tracks_in_order():
    playlist = make_playlist()
    track1 = make_track("track_1")
    track2 = make_track("track_2")

    result = playlist.add_track(track1).add_track(track2)

    assert result.tracks == (track1, track2)


def test_playlist_rejects_duplicate_track_ids() -> None:
    playlist = make_playlist().add_track(make_track("track-001"))
    with pytest.raises(ValueError, match="重複するtrack_id"):
        playlist.add_track(make_track("track-001"))


def test_playlist_removes_tracks_without_mutating_original() -> None:
    first = make_track("track-001")
    second = make_track("track-002")
    playlist = make_playlist().add_track(first).add_track(second)

    result = playlist.remove_track("track-001")

    assert result.tracks == (second,)
    assert playlist.tracks == (first, second)


def test_playlist_moves_track() -> None:
    tracks = [
        make_track(f"track-00{number}") for number in range(1, 4)
    ]
    playlist = make_playlist()
    for track in tracks:
        playlist = playlist.add_track(track)

    result = playlist.move_track(0, 2)

    assert result.tracks == (tracks[1], tracks[2], tracks[0])
    assert playlist.tracks == tuple(tracks)


def test_playlist_reorders_tracks_without_mutating_original() -> None:
    tracks = tuple(
        make_track(f"track-00{number}") for number in range(1, 4)
    )
    playlist = Playlist("playlist_1", "My Playlist", tracks)

    result = playlist.reorder_tracks(("track-003", "track-001", "track-002"))

    assert result.tracks == (tracks[2], tracks[0], tracks[1])
    assert playlist.tracks == tracks


def test_playlist_reorder_rejects_incomplete_track_ids() -> None:
    playlist = make_playlist().add_track(make_track("track-001"))

    with pytest.raises(ValueError, match="ordered_track_ids"):
        playlist.reorder_tracks(("missing-track",))


def test_playlist_renames_and_rejects_blank_names() -> None:
    playlist = make_playlist()
    result = playlist.rename("New Playlist Name")
    assert result.name == "New Playlist Name"
    assert playlist.name == "My Playlist"

    with pytest.raises(ValueError, match="nameは空にできません"):
        playlist.rename("")
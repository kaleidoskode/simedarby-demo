"use client";

/** Movie detail with the Details / Ratings tabs, and the Book Ticket action. */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  BottomBar,
  ErrorNote,
  PosterPlaceholder,
  ScreenHeader,
  Spinner,
  Stars,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { MovieDetail, ReviewList } from "@/lib/types";

export default function MovieDetailPage() {
  const { movieId } = useParams<{ movieId: string }>();

  const [movie, setMovie] = useState<MovieDetail | null>(null);
  const [reviews, setReviews] = useState<ReviewList | null>(null);
  const [tab, setTab] = useState<"details" | "reviews">("details");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    Promise.all([api.getMovie(movieId), api.listReviews(movieId)])
      .then(([detail, reviewList]) => {
        if (cancelled) return;
        setMovie(detail);
        setReviews(reviewList);
        setError(null);
      })
      .catch((cause) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "Could not load the movie");
      });

    return () => {
      cancelled = true;
    };
  }, [movieId, attempt]);

  const retry = () => setAttempt((value) => value + 1);

  if (error) return <ErrorNote message={error} onRetry={retry} />;
  if (!movie || !reviews) return <Spinner label="Loading movie…" />;

  const hours = Math.floor(movie.duration_mins / 60);
  const minutes = movie.duration_mins % 60;

  return (
    <main className="flex min-h-screen flex-col">
      <ScreenHeader title={movie.title} />

      {/* Trailer area. The API returns a URL but hosts no media, so this is a
          placeholder rather than a broken player. */}
      <div className="flex h-44 items-center justify-center bg-surface-raised">
        <span className="flex h-12 w-12 items-center justify-center rounded-full border-2 border-foreground/70 text-lg">
          ▶
        </span>
      </div>

      <div className="flex-1 px-4 pb-6">
        <div className="mt-4 flex gap-3">
          <PosterPlaceholder className="h-32 w-24 shrink-0" />
          <div className="min-w-0">
            <h2 className="text-lg font-semibold leading-tight">{movie.title}</h2>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {movie.genres.map((genre) => (
                <span
                  key={genre}
                  className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted"
                >
                  {genre}
                </span>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-muted">
              {movie.release_date} · {movie.certification} · {hours}h {minutes}m
            </p>
            <div className="mt-1.5 flex items-center gap-2">
              <Stars value={movie.rating_avg} />
              <span className="text-[11px] text-muted">
                {movie.rating_avg}/5 ({movie.rating_count})
              </span>
            </div>
          </div>
        </div>

        <div className="mt-5 flex border-b border-border text-sm">
          {(["details", "reviews"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setTab(value)}
              className={`flex-1 pb-2 transition ${
                tab === value
                  ? "border-b-2 border-foreground font-medium"
                  : "text-muted"
              }`}
            >
              {value === "details" ? "Movie Details" : "Ratings & Reviews"}
            </button>
          ))}
        </div>

        {tab === "details" ? (
          <Details movie={movie} />
        ) : (
          <Reviews reviews={reviews} />
        )}
      </div>

      <BottomBar>
        <Link
          href={`/movies/${movie.id}/book`}
          className="block w-full rounded-lg bg-foreground px-4 py-3.5 text-center text-sm font-semibold text-black transition hover:bg-white"
        >
          Book Ticket
        </Link>
      </BottomBar>
    </main>
  );
}

function Details({ movie }: { movie: MovieDetail }) {
  return (
    <dl className="mt-4 space-y-4 text-sm">
      <Row label="Full synopsis">
        <p className="text-xs leading-relaxed text-muted">{movie.synopsis}</p>
      </Row>
      <Row label="Casts">
        <p className="text-xs text-muted">{movie.casts.join(", ")}</p>
      </Row>
      <Row label="Director">
        <p className="text-xs text-muted">{movie.director}</p>
      </Row>
      <Row label="Writers">
        <p className="text-xs text-muted">{movie.writers.join(", ")}</p>
      </Row>
      <Row label="Format">
        <p className="text-xs text-muted">{movie.formats.join(", ")}</p>
      </Row>
    </dl>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-border pb-3">
      <dt className="mb-1 font-medium">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Reviews({ reviews }: { reviews: ReviewList }) {
  const { breakdown, items } = reviews;

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2">
        <span className="text-2xl font-semibold">{breakdown.average}</span>
        <span className="text-xs text-muted">({breakdown.total} Reviews)</span>
      </div>

      {/* Every bucket including the empty ones, which is why the API returns
          the breakdown separately rather than letting the client tally a page. */}
      <div className="mt-3 space-y-1">
        {[5, 4, 3, 2, 1].map((stars) => {
          const count = breakdown.counts[String(stars)] ?? 0;
          const pct = breakdown.total ? (count / breakdown.total) * 100 : 0;
          return (
            <div key={stars} className="flex items-center gap-2 text-[10px] text-muted">
              <span className="w-8 shrink-0">{"★".repeat(stars)}</span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-raised">
                <span
                  className="block h-full bg-foreground/70"
                  style={{ width: `${pct}%` }}
                />
              </span>
              <span className="w-5 text-right">({count})</span>
            </div>
          );
        })}
      </div>

      <div className="mt-5 space-y-3">
        {items.slice(0, 6).map((review) => (
          <article
            key={review.id}
            className="rounded-lg border border-border bg-surface p-3"
          >
            <Stars value={review.stars} />
            <h3 className="mt-1 text-xs font-semibold">{review.title}</h3>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">{review.body}</p>
            <p className="mt-2 text-[10px] text-muted">— {review.author}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

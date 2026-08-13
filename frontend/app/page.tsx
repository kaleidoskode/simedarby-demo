"use client";

/** Home screen and search — the first two nodes of the flowchart. */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ErrorNote, PosterPlaceholder, Spinner, Stars } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/SessionProvider";
import type { MovieSummary } from "@/lib/types";

const RAILS: { section: "new_release" | "popular" | "recommended"; title: string }[] = [
  { section: "new_release", title: "New Releases" },
  { section: "popular", title: "Popular in cinemas" },
  { section: "recommended", title: "Recommended for you" },
];

export default function HomePage() {
  const { session } = useSession();
  const [movies, setMovies] = useState<MovieSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [attempt, setAttempt] = useState(0);

  // State is only set from the promise callbacks. Setting it synchronously in
  // the effect body would trigger a cascading render, which the React Compiler
  // rules flag.
  useEffect(() => {
    let cancelled = false;

    api
      .listMovies({ limit: 100 })
      .then((page) => {
        if (cancelled) return;
        setMovies(page.items);
        setError(null);
      })
      .catch((cause) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "Could not load movies");
      });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = () => setAttempt((value) => value + 1);

  // Filtering client side keeps typing responsive; `GET /movies?q=` does the
  // same substring match server side and is what a real client would call.
  const searchResults = useMemo(() => {
    if (!query.trim() || !movies) return null;
    const needle = query.trim().toLowerCase();
    return movies.filter((movie) => movie.title.toLowerCase().includes(needle));
  }, [query, movies]);

  return (
    <main className="pb-10">
      <div className="px-4 pt-5">
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 rounded-full bg-surface-raised" />
          <div>
            <p className="text-lg font-semibold">
              Hello, {session?.user.name ?? "there"}
            </p>
            <p className="text-xs text-muted">
              Want to go see a movie? Get your ticket today
            </p>
          </div>
        </div>

        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by movies or cinema hall"
          className="mt-4 w-full rounded-lg border border-border bg-surface px-4 py-3 text-sm outline-none placeholder:text-muted focus:border-accent"
        />
      </div>

      {error && <ErrorNote message={error} onRetry={retry} />}
      {!movies && !error && <Spinner label="Loading movies…" />}

      {movies && searchResults && (
        <Section title={`Results for “${query}”`} movies={searchResults} />
      )}

      {movies &&
        !searchResults &&
        RAILS.map(({ section, title }) => (
          <Section
            key={section}
            title={title}
            movies={movies.filter((movie) => movie.sections.includes(section))}
          />
        ))}
    </main>
  );
}

function Section({ title, movies }: { title: string; movies: MovieSummary[] }) {
  if (movies.length === 0) {
    return (
      <section className="px-4 pt-6">
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="mt-2 text-xs text-muted">Nothing here.</p>
      </section>
    );
  }

  return (
    <section className="px-4 pt-6">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      <div className="grid grid-cols-2 gap-3">
        {movies.map((movie) => (
          <MovieCard key={movie.id} movie={movie} />
        ))}
      </div>
    </section>
  );
}

function MovieCard({ movie }: { movie: MovieSummary }) {
  return (
    <Link
      href={`/movies/${movie.id}`}
      className="group rounded-lg border border-border bg-surface p-2 transition hover:border-accent"
    >
      <PosterPlaceholder className="aspect-[2/3] w-full" />
      <p className="mt-2 line-clamp-2 text-xs font-medium">{movie.title}</p>
      <div className="mt-1 flex items-center gap-1.5">
        <Stars value={movie.rating_avg} />
        <span className="text-[10px] text-muted">{movie.rating_avg}</span>
      </div>
    </Link>
  );
}

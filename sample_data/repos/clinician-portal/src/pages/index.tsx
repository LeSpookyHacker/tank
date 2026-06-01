import { useEffect, useState } from "react";

interface NoteSummary {
  id: string;
  patientLabel: string;
  status: string;
}

export default function ReviewQueue() {
  const [notes, setNotes] = useState<NoteSummary[]>([]);

  useEffect(() => {
    fetch("/api/notes/queue")
      .then((r) => r.json())
      .then(setNotes)
      .catch(() => setNotes([]));
  }, []);

  return (
    <main>
      <h1>Note Review Queue</h1>
      <ul>
        {notes.map((n) => (
          <li key={n.id}>
            {n.patientLabel} — {n.status}
            <a href={`/notes/${n.id}`}>review</a>
          </li>
        ))}
      </ul>
    </main>
  );
}

import type { SourceRecord } from "@genie/contracts";

interface SourceManagerProps {
  sources: SourceRecord[];
  onAdd(files: File[]): Promise<void>;
  onRemove(sourceId: string): Promise<void>;
  onReindex(sourceId: string): Promise<void>;
}

export function SourceManager({ sources, onAdd, onRemove, onReindex }: SourceManagerProps) {
  return (
    <section className="tab-section">
      <div className="section-header">
        <div>
          <h3>Sources</h3>
          <p>Add local knowledge files and keep them indexed for grounded answers.</p>
        </div>
        <label className="primary-button">
          Add Files
          <input
            hidden
            multiple
            type="file"
            accept=".txt,.md,.pdf,.docx,.csv,.xlsx,.png,.jpg,.jpeg,.webp"
            onChange={async (event) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length) {
                await onAdd(files);
              }
              event.currentTarget.value = "";
            }}
          />
        </label>
      </div>
      <div className="source-list">
        {sources.map((source) => (
          <article key={source.id} className="source-card">
            <div>
              <strong>{source.filename}</strong>
              <p>
                {source.status} · {source.chunk_count} chunks
              </p>
            </div>
            <div className="inline-actions">
              <button type="button" onClick={() => onReindex(source.id)}>
                Reindex
              </button>
              <button type="button" className="danger-button" onClick={() => onRemove(source.id)}>
                Remove
              </button>
            </div>
          </article>
        ))}
        {!sources.length ? <p className="empty-copy">No sources yet. Add a file to start grounding answers.</p> : null}
      </div>
    </section>
  );
}


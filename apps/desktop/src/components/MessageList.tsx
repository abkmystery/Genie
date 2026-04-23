import type { ChatResponse } from "@genie/contracts";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

interface MessageListProps {
  messages: Message[];
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="message-list">
      {messages.map((message) => (
        <article key={message.id} className={`message-card ${message.role}`}>
          <header>{message.role === "user" ? "You" : "Genie"}</header>
          <p className="message-body">{message.text}</p>
          {message.response?.evidence?.length ? (
            <div className="evidence-list">
              {message.response.evidence.map((item) => (
                <span key={item.id} className="evidence-chip" title={item.quote ?? ""}>
                  {item.label}
                </span>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

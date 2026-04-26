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

function providerWarning(response?: ChatResponse): string | null {
  const status = response?.provider_diagnostics?.provider_status;
  if (!status || status === "live_gemma") {
    return null;
  }
  if (status === "fallback_mock") {
    return "Offline fallback is answering. Live Gemma is not connected for this request.";
  }
  if (status === "local_not_ready") {
    return "Local Gemma is not ready yet. Warm up the local runner or switch profiles.";
  }
  if (status === "endpoint_error") {
    return "The selected model endpoint returned an error. Check Settings and Debug.";
  }
  return null;
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="message-list">
      {messages.map((message) => {
        const warning = providerWarning(message.response);
        return (
          <article key={message.id} className={`message-card ${message.role}`}>
            <header>{message.role === "user" ? "You" : "Genie"}</header>
            {warning ? <p className="provider-warning">{warning}</p> : null}
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
        );
      })}
    </div>
  );
}

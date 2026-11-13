/* Einzelne Nachricht mit rollenabhängiger Darstellung. */

import type { Message } from "../types";

export function MessageBubble({
  message,
  streaming,
}: {
  message: Message;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex animate-fade-up justify-end">
        <div className="max-w-[78%] rounded-2xl rounded-br-md bg-ink-700 px-4 py-3 text-[14px] leading-relaxed whitespace-pre-wrap text-ink-50">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex animate-fade-up justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-ink-700 bg-ink-850 px-4 py-3 text-[14px] leading-relaxed whitespace-pre-wrap text-ink-100">
        {message.content === "" && streaming ? (
          <span className="inline-flex gap-1 py-1" aria-label="ZENJI denkt">
            <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-jade-500" />
            <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-jade-500 [animation-delay:0.3s]" />
            <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-jade-500 [animation-delay:0.6s]" />
          </span>
        ) : (
          <>
            {message.content}
            {streaming && (
              <span className="ml-0.5 inline-block h-[14px] w-[7px] animate-blink bg-jade-400 align-text-bottom" />
            )}
          </>
        )}
      </div>
    </div>
  );
}

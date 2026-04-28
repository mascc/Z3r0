import { Button, TextArea } from "@douyinfe/semi-ui";
import { Send, Square } from "lucide-react";
import { KeyboardEvent, useState } from "react";

type ComposerProps = {
  streaming: boolean;
  disabled?: boolean;
  onSend: (text: string) => void;
  onInterrupt: () => void;
};

export function Composer({ streaming, disabled = false, onSend, onInterrupt }: ComposerProps) {
  const [text, setText] = useState("");

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || streaming || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    streaming ? onInterrupt() : submit();
  };

  const action = streaming
    ? { icon: <Square size={16} />, type: "danger" as const, label: "Stop", onClick: onInterrupt, disabled: false }
    : { icon: <Send size={16} />, type: "primary" as const, label: "Send", onClick: submit, disabled: disabled || !text.trim() };

  return (
    <div className={`composer${streaming ? " composer-streaming" : ""}`}>
      <TextArea
        value={text}
        onChange={(value) => setText(value)}
        onKeyDown={handleKeyDown}
        autosize={{ minRows: 1, maxRows: 8 }}
        disabled={disabled && !streaming}
        placeholder={
          disabled
            ? "Loading conversation history…"
            : streaming
              ? "Streaming response… press Enter or stop to interrupt"
              : "Send a message — Shift+Enter for newline"
        }
      />
      <Button
        icon={action.icon}
        theme="solid"
        type={action.type}
        onClick={action.onClick}
        disabled={action.disabled}
        aria-label={streaming ? "Interrupt streaming" : "Send message"}
      >
        {action.label}
      </Button>
    </div>
  );
}

"use client";

import { useState, type ComponentProps } from "react";
import { flushSync } from "react-dom";
import { Tabs } from "@base-ui/react/tabs";
import { Markdown } from "@/components/ui/markdown";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

// Markdown field with "Edytuj" / "Podgląd" tabs, like a GitHub comment box.
// Props other than className go to the textarea, so name it with <label htmlFor> or aria-label;
// do not wrap the editor in a <label>, because a click on the label would activate the first tab.
// The textarea stays mounted while previewing, so refs, form submission, and validation keep working.

type MarkdownEditorProps = Omit<ComponentProps<typeof Textarea>, "value"> & {
  value: string;
  textareaClassName?: string;
};

type Mode = "edit" | "preview";

export function MarkdownEditor({ value, className, textareaClassName, onInvalid, ...props }: MarkdownEditorProps) {
  const [mode, setMode] = useState<Mode>("edit");

  return <Tabs.Root value={mode} onValueChange={next => setMode(next as Mode)} className={cn("markdown-editor", className)} data-slot="markdown-editor">
    <Tabs.List className="markdown-editor-tabs" aria-label="Tryb edytora">
      <Tabs.Tab value="edit" className="markdown-editor-tab">Edytuj</Tabs.Tab>
      <Tabs.Tab value="preview" className="markdown-editor-tab">Podgląd</Tabs.Tab>
    </Tabs.List>
    <Tabs.Panel value="edit" keepMounted tabIndex={-1}>
      <Textarea
        value={value}
        className={cn("markdown-editor-input", textareaClassName)}
        // The browser focuses the first invalid field after all invalid events, so reveal it synchronously.
        onInvalid={event => { flushSync(() => setMode("edit")); onInvalid?.(event); }}
        {...props}
      />
    </Tabs.Panel>
    <Tabs.Panel value="preview" className="markdown-editor-preview">
      {value.trim() ? <Markdown text={value} /> : <p className="markdown-editor-empty">Nic do podglądu.</p>}
    </Tabs.Panel>
  </Tabs.Root>;
}

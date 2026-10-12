import React from 'react';

/**
 * Parses markdown-like strings:
 * - **bold**
 * - `code`
 * - ₹ currency amounts
 * - bullet points
 */
export function formatMessageText(text) {
  if (!text) return null;

  const lines = text.split('\n');

  return lines.map((line, lineIdx) => {
    const isBullet = line.trim().startsWith('•') || line.trim().startsWith('-') || line.trim().startsWith('*');
    const cleanLine = isBullet ? line.trim().replace(/^[•\-\*]\s*/, '') : line;

    // Process inline formatting (bold, code, currency)
    const formattedContent = parseInlineFormatting(cleanLine);

    if (isBullet) {
      return (
        <div key={lineIdx} className="formatted-bullet-item">
          <span className="bullet-dot">•</span>
          <span className="bullet-text">{formattedContent}</span>
        </div>
      );
    }

    if (!cleanLine.trim()) {
      return <div key={lineIdx} className="empty-line-spacer" />;
    }

    return (
      <p key={lineIdx} className="formatted-paragraph">
        {formattedContent}
      </p>
    );
  });
}

function parseInlineFormatting(str) {
  if (!str) return '';

  // Regex to match **bold**, `code`, or ₹[0-9,]+
  const regex = /(\*\*.*?\*\*|`.*?`|₹[0-9,]+(?:\.[0-9]+)?)/g;
  const parts = str.split(regex);

  return parts.map((part, i) => {
    if (!part) return null;

    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="text-highlight-bold">{part.slice(2, -2)}</strong>;
    }

    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="inline-code font-mono">{part.slice(1, -1)}</code>;
    }

    if (part.startsWith('₹')) {
      return <span key={i} className="currency-highlight font-mono">{part}</span>;
    }

    return part;
  });
}

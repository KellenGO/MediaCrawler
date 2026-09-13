/** B站投币图标：空心轮廓与实色线条，和结果区的 Lucide 图标保持一致。 */
export function BilibiliCoinIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 28 28"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="14" cy="14" r="10.5" />
      <path d="M9.5 8.5h9M14 8.5v11" />
      <path d="M9.5 16v-1.3c0-2.4 2-4.3 4.5-4.3s4.5 1.9 4.5 4.3V16" />
    </svg>
  );
}

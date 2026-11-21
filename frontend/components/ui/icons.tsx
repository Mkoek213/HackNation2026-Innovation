import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };
function Icon({ size = 20, children, ...props }: IconProps) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" {...props}>{children}</svg>;
}
export const Plus = (props: IconProps) => <Icon {...props}><path d="M12 5v14M5 12h14" /></Icon>;
export const X = (props: IconProps) => <Icon {...props}><path d="m6 6 12 12M6 18 18 6" /></Icon>;
export const Menu = (props: IconProps) => <Icon {...props}><path d="M4 6h16M4 12h16M4 18h16" /></Icon>;
export const Send = (props: IconProps) => <Icon {...props}><path d="m4 11 16-7-7 16-2-7-7-2Zm7 2 9-9" /></Icon>;
export const Mic = (props: IconProps) => <Icon {...props}><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M19 10v1a7 7 0 0 1-14 0v-1M12 19v3" /></Icon>;
export const LogOut = (props: IconProps) => <Icon {...props}><path d="M9 4H4v16h5M9 12h11m-4-4 4 4-4 4" /></Icon>;
export const RadarMark = (props: IconProps) => <Icon {...props}><path d="M20.5 12A8.5 8.5 0 1 1 12 3.5M16 12a4 4 0 1 1-4-4M12 12l6-6" /><circle cx="12" cy="12" r="1.2" fill="currentColor" /></Icon>;
// Knowledge base icons come from Lucide (already a dependency) to keep one stroke style.
export { ArrowLeft, ArrowRight, Building2 as Building, ExternalLink, FileText, FlaskConical, Handshake, Lightbulb, MessagesSquare, Play, Search, Trash2 } from "lucide-react";

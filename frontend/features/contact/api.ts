import { publicPost } from "@/features/workspace";

export type ContactInput = { name: string; email: string; message: string; consent: boolean };
export type ContactField = keyof ContactInput;
export type ContactReceipt = { id: number; created_at: string };

/** Limits mirror backend `ContactCreate`. */
export const limits = { name: { min: 2, max: 120 }, email: { max: 254 }, message: { min: 10, max: 5000 } };

export type SendResult =
  | { ok: true; receipt: ContactReceipt }
  | { ok: false; status: number; fields: ContactField[] };

export async function sendContactMessage(input: ContactInput): Promise<SendResult> {
  const response = await publicPost("contact", input);
  if (response.ok) return { ok: true, receipt: await response.json() };
  let fields: ContactField[] = [];
  if (response.status === 422) {
    try {
      const body: { detail?: { loc?: (string | number)[] }[] } = await response.json();
      fields = (body.detail ?? []).map(item => item.loc?.[1]).filter((field): field is ContactField => typeof field === "string" && field in input);
    } catch {
      // A non-JSON 422 still reports a generic validation failure.
    }
  }
  return { ok: false, status: response.status, fields };
}

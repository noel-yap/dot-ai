// Extraction-for-clarity candidate: the entire access policy is a single
// boolean expression with a ternary chain nested inside it. Reviewers
// cannot tell which rule granted or denied access, and every policy
// change means re-parsing the whole expression. Pure logic — no I/O —
// so the fix is naming the rules, not changing any dependency.
//
// This file is a fixture for the extraction-for-clarity skill evaluation.
// It intentionally exhibits the smells described in the skill's
// "When to use" section.

export interface User {
  id: string;
  role: "viewer" | "editor" | "admin";
  suspended: boolean;
  teamIds: readonly string[];
}

export interface Doc {
  ownerId: string;
  status: "draft" | "published" | "archived";
  teamId: string;
  locked: boolean;
  allowTeamEdits: boolean;
}

export function canEditDocument(user: User, doc: Doc): boolean {
  return (
    !user.suspended &&
    doc.status !== "archived" &&
    (user.role === "admin"
      ? !doc.locked || doc.ownerId === user.id
      : user.role === "editor"
        ? !doc.locked &&
          (doc.ownerId === user.id ||
            (doc.allowTeamEdits &&
              user.teamIds.includes(doc.teamId) &&
              doc.status === "draft"))
        : false)
  );
}

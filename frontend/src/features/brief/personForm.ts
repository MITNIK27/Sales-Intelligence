// The "Add a person" form: the same checks the server makes, so a mistake is explained next to the
// field instead of coming back as a server error.

export type PersonForm = {
  fullName: string;
  roleTitle: string;
  linkedinUrl: string;
  email: string;
};

export const EMPTY_PERSON: PersonForm = {
  fullName: "",
  roleTitle: "",
  linkedinUrl: "",
  email: "",
};

export type PersonErrors = Partial<Record<keyof PersonForm, string>>;

export function validatePerson(form: PersonForm): PersonErrors {
  const errors: PersonErrors = {};
  if (form.fullName.trim().length < 2) errors.fullName = "Enter their name.";
  if (form.roleTitle.trim().length < 2)
    errors.roleTitle = "Enter their job title; it is how their role is judged.";
  const linkedin = form.linkedinUrl.trim();
  if (linkedin && !linkedin.toLowerCase().includes("linkedin.com/in/"))
    errors.linkedinUrl = "Use a profile link, like linkedin.com/in/name.";
  const email = form.email.trim();
  if (email && (!email.includes("@") || email.includes(" ")))
    errors.email = "This does not look like an email address.";
  return errors;
}

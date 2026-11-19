export const APP_NAME = "Sales Intelligence";
// The short form used where the product speaks for itself, for example "Suggested by SI". Change it
// here when the product gets its name.
export const APP_SHORT_NAME = "SI";

// Wording that speaks as the product. Screens call these instead of typing the name into a
// string, so the product's final name is set once (APP_SHORT_NAME) and every one of them
// follows. Add a function here for each new line of wording that names the product.
export const suggestedBy = () => `Suggested by ${APP_SHORT_NAME}`;
export const recommendedAreasLabel = () =>
  `${APP_SHORT_NAME} recommended areas`;
export const refreshRecommendationsLabel = () =>
  `Refresh ${APP_SHORT_NAME} recommendations`;
// Kept in sync with package.json's "version" field manually — importing package.json
// here would pull a file outside tsconfig's "include": ["src"] root into the build.
export const APP_VERSION = "0.1.0";
export const COPYRIGHT_YEAR = new Date().getFullYear();
export const COPYRIGHT_OWNER = "InfoBeans Technologies Limited";

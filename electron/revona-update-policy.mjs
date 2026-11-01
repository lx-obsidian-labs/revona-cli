// Revona has no trusted update feed yet. Never use an inherited upstream feed.
// The upstream application remains unaffected while the fork is developed.
export function revonaUpdatesDisabled({ packaged, appName }) {
  return packaged === true && appName === "Revona Bot";
}

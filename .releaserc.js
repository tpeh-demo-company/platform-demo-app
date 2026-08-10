module.exports = {
  branches: ["main"],
  plugins: [
    [
      "semantic-release-scope-filter",
      {
        scopes: ["demo-app"],
        filterOutMissingScope: true,
      },
    ],
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    [
      "@semantic-release/changelog",
      {
        changelogFile: "CHANGELOG.md",
      },
    ],
    [
      "@semantic-release/git",
      {
        assets: ["CHANGELOG.md"],
        message: "chore: release ${nextRelease.version} [skip ci]",
      },
    ],
    "@semantic-release/github",
  ],
};

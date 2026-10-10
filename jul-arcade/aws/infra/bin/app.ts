import { App } from "aws-cdk-lib";
import { ArcadeStack, Packaging } from "../lib/arcade-stack";

const app = new App();
const packaging = (app.node.tryGetContext("packaging") ?? "zip") as Packaging;
if (packaging !== "zip" && packaging !== "container") throw new Error(`-c packaging=zip|container, got ${packaging}`);

// one stack per mode, so both can live side by side and be compared
new ArcadeStack(app, packaging === "zip" ? "JulArcade" : "JulArcadeContainer", {
  packaging,
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? "eu-west-1" },
});

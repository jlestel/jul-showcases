import * as fs from "node:fs";
import * as path from "node:path";
import { CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import { Construct } from "constructs";

const BUILD = path.join(__dirname, "..", "..", "build");
/** 1,769 MB = one full vCPU, the best price per call in jul's docs/aws-lambda.md. */
const MODEL_MEMORY_MB = 1769;

export type Packaging = "zip" | "container";

export interface ArcadeProps extends StackProps {
  /** zip: two functions, one model each (jul's recommendation). container: one image, both models. */
  packaging: Packaging;
}

/**
 * JuL Arcade on AWS:
 *   CloudFront ─┬─ /*      → S3 (the game page, private bucket, origin access control)
 *               └─ /api/*  → API Gateway REST (stage "api") → game Lambda (engine + levels)
 *                                                               └─ invokes the model Lambda(s)
 * The game Lambda has no model: each block of the player's machine is one invocation of a model
 * function (Choice → vectors, Noul/Score → cross model). No auth yet: the API's methods are open, an
 * authorizer (Cognito, social login) goes on `api.root` later.
 * Build first: aws/scripts/build.sh (and Docker running for packaging=container).
 */
export class ArcadeStack extends Stack {
  constructor(scope: Construct, id: string, props: ArcadeProps) {
    super(scope, id, props);
    for (const dir of ["game", "web", props.packaging === "zip" ? "choice" : "container"]) {
      if (!fs.existsSync(path.join(BUILD, dir))) throw new Error(`build/${dir} missing: run aws/scripts/build.sh first`);
    }
    const logGroup = (name: string) =>
      new logs.LogGroup(this, `${name}Logs`, { retention: logs.RetentionDays.ONE_WEEK, removalPolicy: RemovalPolicy.DESTROY });
    const modelEnv = { JUL_ONNX_THREADS: String(Math.max(1, Math.floor(MODEL_MEMORY_MB / 1769))) };

    // --- the model functions ----------------------------------------------------------------------
    let choiceFn: lambda.IFunction, crossFn: lambda.IFunction;
    if (props.packaging === "zip") {
      const zipFn = (name: string, dir: string, role: string) =>
        new lambda.Function(this, name, {
          runtime: lambda.Runtime.PYTHON_3_12,
          architecture: lambda.Architecture.ARM_64,
          handler: "model_handler.handler",
          code: lambda.Code.fromAsset(path.join(BUILD, dir)),
          memorySize: MODEL_MEMORY_MB,
          timeout: Duration.seconds(30),
          environment: { ...modelEnv, ROLE: role },
          logGroup: logGroup(name),
        });
      choiceFn = zipFn("ChoiceModel", "choice", "choice");
      crossFn = zipFn("CrossModel", "cross", "cross");
    } else {
      const both = new lambda.DockerImageFunction(this, "Model", {
        code: lambda.DockerImageCode.fromImageAsset(path.join(BUILD, "container")),
        architecture: lambda.Architecture.ARM_64,
        memorySize: MODEL_MEMORY_MB,
        timeout: Duration.seconds(30),
        environment: { ...modelEnv, ROLE: "both" },
        logGroup: logGroup("Model"),
      });
      choiceFn = crossFn = both;
    }

    // --- the game API ---------------------------------------------------------------------------
    const game = new lambda.Function(this, "Game", {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: "game_handler.handler",
      code: lambda.Code.fromAsset(path.join(BUILD, "game")),
      memorySize: 256,
      // a wave is ~20-40 decisions, each a model invocation (a few ms warm, a cold start at worst)
      timeout: Duration.seconds(29),
      environment: { CHOICE_FN: choiceFn.functionName, CROSS_FN: crossFn.functionName },
      logGroup: logGroup("Game"),
    });
    choiceFn.grantInvoke(game);
    if (crossFn !== choiceFn) crossFn.grantInvoke(game);

    // stage "api": CloudFront forwards /api/* unchanged, so the paths line up without rewriting
    const api = new apigw.LambdaRestApi(this, "Api", {
      handler: game,
      proxy: false,
      deployOptions: { stageName: "api", throttlingRateLimit: 20, throttlingBurstLimit: 40 },
      endpointConfiguration: { types: [apigw.EndpointType.REGIONAL] },
    });
    api.root.addResource("levels").addMethod("GET");
    api.root.addResource("play").addMethod("POST");
    api.root.addResource("warmup").addMethod("GET");

    // --- the front ------------------------------------------------------------------------------
    const site = new s3.Bucket(this, "Site", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    const apiOrigin = new origins.RestApiOrigin(api, { originPath: "" });
    const cdn = new cloudfront.Distribution(this, "Cdn", {
      defaultRootObject: "index.html",
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(site),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      additionalBehaviors: {
        "/api/*": {
          origin: apiOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
    });
    new s3deploy.BucketDeployment(this, "SiteFiles", {
      sources: [s3deploy.Source.asset(path.join(BUILD, "web"))],
      destinationBucket: site,
      distribution: cdn,
      distributionPaths: ["/*"],
    });

    new CfnOutput(this, "Url", { value: `https://${cdn.distributionDomainName}` });
    new CfnOutput(this, "ApiUrl", { value: api.url });
    new CfnOutput(this, "Packaging", { value: props.packaging });
    new CfnOutput(this, "ChoiceFunction", { value: choiceFn.functionName });
    new CfnOutput(this, "CrossFunction", { value: crossFn.functionName });
  }
}

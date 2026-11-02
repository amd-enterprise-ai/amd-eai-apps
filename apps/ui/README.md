<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# UI Applications

This directory contains the Next.js-based frontend applications for AMD enterprise AI reference stack, organized as a monorepo using Turborepo and pnpm workspaces.

## Structure

```
apps/ui/
├── airm/          # AI Resource Manager UI
├── aiwb/          # AI Workbench UI
└── shared/        # Shared components and utilities
```

## Applications

### AIRM (AI Resource Manager)

- **Port**: 8010 (development)
- **Package**: `airm-ui`
- Enterprise AI resource management interface

### AIWB (AI Workbench)

- **Port**: 8011 (development)
- **Package**: `aiwb-ui`
- Enterprise AI development workbench interface

## Prerequisites

- **Node.js**: 18.x or later
- **pnpm**: whatever the `packageManager` pin in `apps/ui/package.json` names — run it through corepack rather than an ambient install, so regenerating the lockfile uses the pinned version
- **Package Manager**: This project uses pnpm workspaces

## Getting Started

### Install Dependencies

```bash
# From the /apps/ui directory
pnpm install
```

### Development

Run all applications in development mode:

```bash
pnpm dev
```

Run individual applications:

```bash
# AI Resource Manager
pnpm dev:airm

# AI Workbench
pnpm dev:aiwb
```

Applications will be available at:

- AIRM: http://localhost:8010
- AIWB: http://localhost:8011

### Building

Build all applications:

```bash
pnpm build
```

Build individual applications:

```bash
pnpm build:airm
pnpm build:aiwb
```

### Testing

```bash
# Run all tests
pnpm test

# Type checking
pnpm typecheck
```

### Linting and Formatting

```bash
# Run linting across all apps
pnpm lint
```

Each individual app has additional formatting scripts using Biome.

## Technology Stack

- **Framework**: Next.js 16 with Turbopack
- **UI Library**: HeroUI (Next.js optimized)
- **State Management**: TanStack Query (React Query)
- **Forms**: React Hook Form with Zod validation
- **Styling**: Tailwind CSS 4
- **Icons**: Tabler Icons React
- **Testing**: Vitest with Testing Library
- **Authentication**: NextAuth.js
- **Internationalization**: next-i18next
- **Build Tool**: Turborepo
- **Package Manager**: pnpm

## Workspace Configuration

### Turborepo

The monorepo uses Turborepo for task orchestration. Key features:

- Parallel task execution
- Intelligent caching
- Task dependencies and pipelines

### PNPM Workspaces

Workspaces are defined in `pnpm-workspace.yaml`:

- `airm` - AI Resource Manager app
- `aiwb` - AI Workbench app
- `shared/**` - Shared packages and components

## Shared Resources

The `shared/` directory contains reusable code across applications:

- **assets**: Images, fonts, and static resources
- **components**: Reusable React components
- **hooks**: Custom React hooks
- **layouts**: Common layout components
- **scripts**: Code generation scripts
- **tailwind-config**: Shared Tailwind configuration
- **types**: TypeScript type definitions
- **utils**: Utility functions and helpers

## Development Guidelines

### Shared Component Translations

Translations owned by `@amdenterpriseai/components` live in
`shared/components/locales/`. Each app resolves the `sharedComponents`
namespace from that directory through its `next-i18next.config.js`; do not add
copies under an app's `public/locales/`. App-owned strings remain in the app's
feature namespace, even when the English text matches a shared-component
string.

`sharedComponents.json` is grouped by what a string is for (`actions`, `data`,
`status`, `menu`) rather than by owning component, so text reused across
components stays in one place. Add a component-named group only when the
strings are specific to that component, as `TagInput` and `FormFileUpload` are.

Pages must load translations through the app's `getPageTranslations` helper,
which always serializes `common` and `sharedComponents` for client hydration.
Direct `serverSideTranslations` imports in pages fail the namespace check.
Keep each config's explicit `ns` list in sync when adding a namespace; app
typechecks validate those lists, that the helper's defaults match
`DEFAULT_PAGE_NAMESPACES`, that every namespace resolved from the shared locale
root is listed in `SHARED_NAMESPACES`, and that every namespace a page requests
exists.

The shared config scripts and the shared locale root must reach the production
image as whole directories, because the modules inside each require their
siblings. Copying individual files instead ships a module without its
dependency, which surfaces only as a runtime `MODULE_NOT_FOUND` in the
container; the namespace check fails the build if a Dockerfile narrows them.

### Adding a New Shared Component

1. Create component in `shared/components/`
2. Export from the appropriate shared package
3. Import in application using workspace protocol: `@amdenterpriseai/components`

### Environment Variables

Each application (airm/aiwb) should have its own `.env.local` file. See individual app READMEs for specific variables.

### Component Development

Both applications support Ladle for component development:

```bash
cd airm  # or aiwb
pnpm ladle
```

## Production Deployment

Build for production:

```bash
pnpm build
```

Start production server:

```bash
cd airm  # or aiwb
pnpm start
```

Production builds run on port 8000 by default.

## Troubleshooting

### Port Already in Use

If ports 8010 or 8011 are in use, kill the process or modify the port in the respective `package.json` scripts.

### Dependencies Not Resolving

```bash
# Clean install
rm -rf node_modules
pnpm install
```

### Build Cache Issues

```bash
# Clear Turborepo cache
rm -rf .turbo
pnpm build
```

## Related Documentation

- [AIRM Application](./airm/README.md)
- [AIWB Application](./aiwb/README.md)
- [Turborepo Documentation](https://turbo.build/repo/docs)
- [Next.js Documentation](https://nextjs.org/docs)

## License

See [LICENSE.TXT](../../LICENSE.TXT) in the repository root.

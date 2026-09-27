# Fragment — get a personalized flyer into the cart

Shared setup steps, reused by any ticket via `Setup : add-flyer-to-cart`. Only the arrange part
lives here (pick a template, run through the studio, add to cart, reach the cart page); each ticket
keeps its own act + assertions. Every ticket that includes this runs these steps itself, so the
tickets stay independent — no test ever inherits another test's cart.

1. If a country banner appears, click "Close".
2. Click "Browse our templates".
3. Open one of the "Flyers templates".
4. Click "Edit my design".
5. Click "Next".
6. Click "Continue without Back".
7. Check the box "I have reviewed and approve my design".
8. Click "Continue".
9. Click "Add to cart".
10. Click "Continue".
11. Click "Continue to cart".

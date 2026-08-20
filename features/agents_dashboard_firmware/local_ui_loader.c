/* Local-only AGENTS page applicator.
 *
 * The page assembly has already selected a frozen embedded GIF.  This helper
 * deliberately performs no file, network, timer, or persistent-state work.
 */

#define ATTR_ENTRY __attribute__((section(".text.entry"), noinline, used))

ATTR_ENTRY int ap01_agents_apply_current(void *argument)
{
  return argument != (void *)0;
}

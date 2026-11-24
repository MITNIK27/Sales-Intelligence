import { ChevronDown, LogOut, UserRound, UsersRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { ACTIONS, ROLE_LABEL } from "@/auth/types";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { initials } from "@/features/users/userLabels";
import { cn } from "@/lib/utils";

// The signed-in person, top right: their initials in a circle. Opening it shows who they are and
// their role, a link to their profile (and to User Management for those who run it), and sign out.
export function UserMenu({ limited = false }: { limited?: boolean }) {
  const { me, can, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  if (!me) return null;
  const name = me.name ?? me.user?.display_name ?? me.email;
  const letters = initials(me.name ?? me.user?.display_name, me.email);
  const role = me.user ? ROLE_LABEL[me.user.role] : "No access yet";

  const item =
    "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm hover:bg-muted focus-visible:bg-muted focus-visible:outline-none";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Account: ${name}`}
          className="group flex items-center gap-2 rounded-full py-1 pl-1 pr-2.5 text-sm transition-colors duration-150 hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary data-[state=open]:bg-muted motion-reduce:transition-none"
        >
          <span
            className="grid size-8 place-items-center rounded-full bg-sidebar text-xs font-semibold text-white"
            aria-hidden="true"
          >
            {letters}
          </span>
          <span className="hidden max-w-32 truncate font-medium sm:inline">
            {name.split(/[\s@]/)[0]}
          </span>
          <ChevronDown
            className="size-4 text-muted-foreground transition-transform duration-150 group-data-[state=open]:rotate-180"
            aria-hidden="true"
          />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0">
        <div className="flex items-center gap-3 border-b border-border p-4">
          <span
            className="grid size-11 shrink-0 place-items-center rounded-full bg-sidebar text-base font-semibold text-white"
            aria-hidden="true"
          >
            {letters}
          </span>
          <div className="min-w-0">
            <div className="truncate font-semibold">{name}</div>
            <div className="truncate text-xs text-muted-foreground">
              {me.email}
            </div>
            <span
              className={cn(
                "mt-1 inline-block px-2 py-0.5 text-[11px] font-semibold",
                me.user
                  ? "bg-accent text-primary-text"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {role}
            </span>
          </div>
        </div>
        <div className="py-1">
          {!limited && (
            <Link to="/profile" className={item} onClick={() => setOpen(false)}>
              <UserRound className="size-4 text-muted-foreground" />
              View profile
            </Link>
          )}
          {!limited && can(ACTIONS.usersManage) && (
            <Link to="/users" className={item} onClick={() => setOpen(false)}>
              <UsersRound className="size-4 text-muted-foreground" />
              User management
            </Link>
          )}
          <button
            type="button"
            className={cn(item, "text-destructive")}
            onClick={() => {
              setOpen(false);
              void signOut();
            }}
          >
            <LogOut className="size-4" />
            Sign out
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

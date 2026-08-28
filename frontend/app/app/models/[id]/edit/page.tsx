"use client";
import { useParams } from "next/navigation";
import { ModelProfileForm } from "../../../../../components/model-profile-form";
export default function EditModelPage() { const params = useParams<{ id: string }>(); return <ModelProfileForm id={params.id} />; }
